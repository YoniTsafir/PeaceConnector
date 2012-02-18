#!/usr/bin/env python

FACEBOOK_APP_ID = "105470519580554"
FACEBOOK_APP_SECRET = "d23ef0731fa99355d36a29994a84d170"

import base64
import cgi
import Cookie
import email.utils
import hashlib
import hmac
import logging
import os.path
import time
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
        if not hasattr(self, "_current_user"):
            self._current_user = None
            user_id = parse_cookie(self.request.cookies.get("fb_user"))
            if user_id:
                self._current_user = User.get_by_key_name(user_id)
        return self._current_user


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
            response = cgi.parse_qs(urllib.urlopen(
                "https://graph.facebook.com/oauth/access_token?" +
                urllib.urlencode(args)).read())
            access_token = response["access_token"][-1]

            profile = json.load(urllib.urlopen(
                "https://graph.facebook.com/me?" +
                urllib.urlencode(dict(access_token=access_token))))
            
            birthday = datetime.date(profile["birthday"])
            logging.error("birthday: %s", birthday)
            
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
            
            user = User(key_name=str(profile["id"]), fb_id=str(profile["id"]),
                        name=profile["name"], access_token=access_token,
                        profile_url=profile["link"], email=profile["email"], 
                        birthday=birthday, country=country,
                        work_position_ids=work_position_ids, 
                        education_concentrations_ids=education_concentrations_ids,
                        likes_ids=likes_ids)
            
            user.put()
            
            set_cookie(self.response, "fb_user", str(profile["id"]),
                       expires=time.time() + 30 * 86400)
            
            # TODO: start searching for matches in DB, in another thread...
            
            self.redirect("/")
        else:
            self.redirect(
                "https://graph.facebook.com/oauth/authorize?" +
                urllib.urlencode(args))


class LogoutHandler(BaseHandler):
    def get(self):
        set_cookie(self.response, "fb_user", "", expires=time.time() - 86400)
        self.redirect("/")


def set_cookie(response, name, value, domain=None, path="/", expires=None):
    """Generates and signs a cookie for the give name/value"""
    timestamp = str(int(time.time()))
    value = base64.b64encode(value)
    signature = cookie_signature(value, timestamp)
    cookie = Cookie.BaseCookie()
    cookie[name] = "|".join([value, timestamp, signature])
    cookie[name]["path"] = path
    if domain: cookie[name]["domain"] = domain
    if expires:
        cookie[name]["expires"] = email.utils.formatdate(
            expires, localtime=False, usegmt=True)
    response.headers._headers.append(("Set-Cookie", cookie.output()[12:]))


def parse_cookie(value):
    """Parses and verifies a cookie value from set_cookie"""
    if not value: return None
    parts = value.split("|")
    if len(parts) != 3: return None
    if cookie_signature(parts[0], parts[1]) != parts[2]:
        logging.warning("Invalid cookie signature %r", value)
        return None
    timestamp = int(parts[1])
    if timestamp < time.time() - 30 * 86400:
        logging.warning("Expired cookie %r", value)
        return None
    try:
        return base64.b64decode(parts[0]).strip()
    except:
        return None


def cookie_signature(*parts):
    """Generates a cookie signature.

    We use the Facebook app secret since it is different for every app (so
    people using this example don't accidentally all use the same secret).
    """
    cookie_hash = hmac.new(FACEBOOK_APP_SECRET, digestmod=hashlib.sha1)
    for part in parts: cookie_hash.update(part)
    return cookie_hash.hexdigest()


def main():
    util.run_wsgi_app(webapp.WSGIApplication([
        (r"/", HomeHandler),
        (r"/auth/login", LoginHandler),
        (r"/auth/logout", LogoutHandler),
    ], debug=True))


if __name__ == "__main__":
    main()
