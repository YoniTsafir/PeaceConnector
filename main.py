#!/usr/bin/env python

FACEBOOK_APP_ID = "105470519580554"
FACEBOOK_APP_SECRET = "d23ef0731fa99355d36a29994a84d170"

import cgi
import logging
import os.path
import urllib
import re
import datetime

from django.utils import simplejson as json
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import util
from google.appengine.ext.webapp import template

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


class HomeHandler(BaseHandler):
    def get(self):
        path = os.path.join(os.path.dirname(__file__), "template.html")
        args = dict(current_user=self.current_user)
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

        if self.request.get("code"):
            args["client_secret"] = FACEBOOK_APP_SECRET
            args["code"] = self.request.get("code")

            logging.info("Facebook login phase 2")
            
            response = cgi.parse_qs(urllib.urlopen(
                "https://graph.facebook.com/oauth/access_token?" +
                urllib.urlencode(args)).read())
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
                                        
            country = re.match(".*<country>(.*)</country>.*", 
                               country_raw.read(), 
                               re.MULTILINE | re.DOTALL).groups()[0].strip()
            
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
            
            # TODO: start searching for matches in DB, in another thread...
            
            logging.info("Redirectring back to home")
            self.redirect("/?user=%s" % user.key())
        else:
            logging.info("Redirecting to facebook login")
            self.redirect(
                "https://graph.facebook.com/oauth/authorize?" +
                urllib.urlencode(args))

def main():
    util.run_wsgi_app(webapp.WSGIApplication([
        (r"/", HomeHandler),
        (r"/auth/login", LoginHandler),
    ], debug=True))


if __name__ == "__main__":
    main()
