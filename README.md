PeaceConnector
==============

This is a project that was initially prepared for the [Innovation Israel Hackathon 2012][hackathon]

Platform
--------
This is a GAE python app that integrates with Facebook. 

How it works
------------
Users log in and allow the app access to their profile info and their likes, then the app tries to match them with another user from a country that is defined in a conflict with the original user (see `conflicts_dict.py`) according to common likes/birth date/work experience/fields of study.

If a match is found, an email will sent to both users telling them what they.


[hackathon]: http://www.innovationisrael.com/hackathon
