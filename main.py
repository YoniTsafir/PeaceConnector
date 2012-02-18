#!/usr/bin/env python

FACEBOOK_APP_ID = "105470519580554"
FACEBOOK_APP_SECRET = "d23ef0731fa99355d36a29994a84d170"

import cgi
import logging
import os.path
import urllib
import re
import datetime
import random

from django.utils import simplejson as json
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template
from google.appengine.api import taskqueue

from conflicts_dict import CONFLICTS_DICT

class User(db.Model):
    fb_id = db.StringProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    updated = db.DateTimeProperty(auto_now=True)
    name = db.StringProperty(required=True)
    profile_url = db.StringProperty(required=True)
    access_token = db.StringProperty(required=True)
    email = db.EmailProperty(required=True)
    country = db.StringProperty(required=True)
    birthday = db.DateProperty(required=True)
    work_position_ids = db.StringListProperty(required=True)
    education_concentrations_ids = db.StringListProperty(required=True)
    likes_ids = db.StringListProperty(required=True)
    
class BaseHandler(webapp.RequestHandler):
    @property
    def current_user(self):
        """Returns the logged in Facebook user, or None if unconnected."""
        if self.request.get("user"):
            return User.get(self.request.get("user"))
        
        return None
    
    @property
    def ask_for_country(self):
        return self.request.get("ask_for_country")

    @property
    def code(self):
        return self.request.get("code")

class HomeHandler(BaseHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), "template.html")
        args = dict(current_user=self.current_user, 
                    ask_for_country=self.ask_for_country,
                    code=self.code)
        self.response.out.write(template.render(path, args))


class LoginHandler(BaseHandler):
    def get(self):
        if self.request.get("error"):
            self.response.out.write(self.request.get("error_description"))
            return
        
        args = dict(client_id=FACEBOOK_APP_ID, 
                    redirect_uri=self.request.path_url,
                    scope="user_about_me,user_birthday,user_education_history,"
                          "user_likes,user_location,user_work_history,email")

        if self.code:
            args["client_secret"] = FACEBOOK_APP_SECRET
            args["code"] = self.code

            logging.info("Facebook login phase 2")
            
            response = cgi.parse_qs(urllib.urlopen(
                "https://graph.facebook.com/oauth/access_token?" +
                urllib.urlencode(args)).read())
            
            logging.info("Phase 2 response: %s", response)
            access_token = response["access_token"][-1]

            logging.info("Loading basic info")
            profile = json.load(urllib.urlopen(
                "https://graph.facebook.com/me?" +
                urllib.urlencode(dict(access_token=access_token))))
            
            birthday = datetime.datetime.strptime(profile["birthday"], "%m/%d/%Y").date()
            
            logging.info("Loading country")
            country_raw = urllib.urlopen(
                "https://api.facebook.com/method/fql.query?" +
                urllib.urlencode(dict(query="SELECT current_location.country FROM user WHERE uid=" + profile["id"],
                                      access_token=access_token)))

            country = self.request.get("country")
            if not country:
                country_match = re.match(".*<country>(.*)</country>.*", 
                                         country_raw.read(), 
                                         re.MULTILINE | re.DOTALL)
                if country_match:
                    country = country_match.groups()[0].strip()
                else:
                    logging.warn("Couldn't get country from facebook, asking directly instead")
                    self.redirect("/?" + urllib.urlencode(dict(code=self.code, ask_for_country=True)))
                    return
            
            work_position_ids = []
            if "work" in profile:
                for workplace in profile["work"]:
                    if "position" in workplace:
                        work_position_ids.append(workplace["position"]["id"])
            
            education_concentrations_ids = []
            if "education" in profile:
                for education_item in profile["education"]:
                    if "concentration" in education_item:
                        for concentration in education_item["concentration"]:
                            education_concentrations_ids.append(concentration["id"])

            logging.info("Fetching user's likes")
            all_likes = json.load(urllib.urlopen(
                "https://graph.facebook.com/me/likes?" +
                urllib.urlencode(dict(access_token=access_token))))["data"]
            
            likes_ids = [like["id"] for like in all_likes]
            
            logging.info("Saving user to DB")
            user = User(key_name=str(profile["id"]), fb_id=str(profile["id"]),
                        name=profile["name"], access_token=access_token,
                        profile_url=profile["link"], email=profile["email"], 
                        birthday=birthday, country=country,
                        work_position_ids=work_position_ids, 
                        education_concentrations_ids=education_concentrations_ids,
                        likes_ids=likes_ids)
            
            user.put()
            
            logging.info("Queueing match task")
            taskqueue.add(url="/match", params={ "user" : user.key() })
            
            logging.info("Redirectring back to home")
            self.redirect("/?user=%s" % user.key())
        else:
            logging.info("Redirecting to facebook login")
            self.redirect(
                "https://graph.facebook.com/oauth/authorize?" +
                urllib.urlencode(args))

class MatchHandler(webapp.RequestHandler):
    def post(self):
        user_key = self.request.get("user")
        user_to_match = User.get(user_key)
        if user_to_match and user_to_match.country in CONFLICTS_DICT:
            conflicting_countries = CONFLICTS_DICT[user_to_match.country]
            users_from_opposite_countries = User.all().filter("country IN ", conflicting_countries)
            random.shuffle(list(users_from_opposite_countries))
            for user in users_from_opposite_countries:
                in_common = self._find_common_grounds(user_to_match, user)
                if (len(in_common) > 0):
                    logging.info("Found a match between '%s' and '%s'", user_to_match.name, user.name)
                    self._send_email(user_to_match, user, in_common)
                    return
            
        logging.info("Couldn't find a match for '%s'", user_to_match.name)
        

    def _find_intersecting_ids(self, user1, user2, common_grounds, id_list_attr, verb):
        for object_id in getattr(user1, id_list_attr):
            if object_id in getattr(user2, id_list_attr):
                logging.info("Fetching name of common object: " + object_id)
                parsed_object = json.load(urllib.urlopen("https://graph.facebook.com/" + object_id + "?" +
                                                       urllib.urlencode(dict(access_token=user1.access_token))))
                logging.info("PARSED: " + str(parsed_object))
                common_grounds.append("You both %s %s" % (verb, parsed_object["name"]))

    def _find_common_grounds(self, user1, user2):
        common_grounds = list()
        
        if user1.birthday.day == user2.birthday.day and \
                user1.birthday.month == user2.birthday.month:
            common_grounds.append("You both have the same birthday")
        
        if user1.birthday.year == user2.birthday.year:
            common_grounds.append("You were both born on %d", user1.birthday.year)
        
        self._find_intersecting_ids(user1, user2, common_grounds, "likes_ids", "like")
        self._find_intersecting_ids(user1, user2, common_grounds, "education_concentrations_ids", "studied")
        self._find_intersecting_ids(user1, user2, common_grounds, "work_position_ids", "worked as a")
        
        return common_grounds
        
    def _send_email(self, user1, user2, in_common):
        logging.info("Sending email: %s and %s have in common: %s", user1.name, user2.name, in_common)

        #TODO: implement for real

    
def main():
    util.run_wsgi_app(webapp.WSGIApplication([
        (r"/", HomeHandler),
        (r"/auth/login", LoginHandler),
        (r"/match", MatchHandler),
    ], debug=True))


if __name__ == "__main__":
    main()