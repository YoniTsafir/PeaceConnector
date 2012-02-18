ARAB_COUNTRIES = ["Egypt", "Iran", "Turkey", "Sudan", "Algeria", "Morocco", "Iraq", "Saudi Arabia",
                  "Yemen", "Syria", "Libya", "Jordan", "United Arab Emirates", "Lebanon", "Palestinian territories",
                  "Palestinian Territory", "Palestine", "Kuwait", "Oman", "Qatar", "Bahrain", "Afghanistan", "Gaza"]

WESTERN_COUNTRIES = ["Israel", "United States", "England", "France"]

CONFLICTS_DICT = {}

for country in ARAB_COUNTRIES:
    CONFLICTS_DICT[country] = WESTERN_COUNTRIES

for country in WESTERN_COUNTRIES:
    CONFLICTS_DICT[country] = ARAB_COUNTRIES

CONFLICTS_DICT["United States"] += ["North Korea", "Cuba"]
CONFLICTS_DICT["North Korea"] = ["South Korea", "United States"]
CONFLICTS_DICT["South Korea"] = ["North Korea"]
CONFLICTS_DICT["Russia"] = ["Georgia"]
CONFLICTS_DICT["Georgia"] = ["Russia"]