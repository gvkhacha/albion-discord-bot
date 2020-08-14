import json
import urllib.request
import re
from collections import namedtuple
from os import path

"""
This file fetches item data from albion online data's github page (JSON) and searches through it and adds common names
Common names are usually in the form of tier/enchant. For example, you would not write "Adept's Dagger@1" or "T4_ADEPTS_DAGGER@1" but 
simply "T4.1 dagger". 

Plus, this will remove all the extra http fetches per request. If you want to update the items, simply remove items.json from the directory.
"""

TIER_REGEX = r"(?:T(\d))_(\w+)(?:@(\d))?" # Extracts tier, name, and item ID
ItemName = namedtuple("ItemName", "tier, name, enchant", defaults=(1, None, 0)) # Groups them together in namedtouple
TIER_LONG_NAMES = {"Journeyman's", "Adept's", "Expert's", "Master's", "Grandmaster's", "Elder's"} # Will replace with t3-8
ENC_LONG_NAMES = {"Uncommon", "Rare", "Exceptional", "Cured"} # Will replace with enchant 1-3 (usually resources, WIP)
RESOURCE_NAMES = {"Birch", "Pine", "Cedar", "Bloodoak", "Ashenbark", "Whitewood", "Copper", "Tin", "Iron", "Titatnium", "Runite", "Meteorite", "Adamantium", "Rugged", "Thin", "Medium", "Heavy", "Robust", "Thick", "Resilient", "Bronze", "Stiff", "Thick", "Worked", "Cured", "Hardened", "Reinforced", "Fortified", "Simple", "Neat", "Fine", "Ornate", "Lavish", "Opulent", "Baroque"}

def _tryInt(number: str, default: int) -> int:
    try:
        return int(number)
    except ValueError:
        return default

def _getItemData() -> [dict]:
    url = "https://raw.githubusercontent.com/broderickhyman/ao-bin-dumps/master/formatted/items.json"
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())


def _convertItem(name: str) -> ItemName:
    matches = re.findall(TIER_REGEX, name)
    if len(matches) > 0:
        tier, n, enchant = matches[0]
        item = ItemName(_tryInt(tier, 1), n, _tryInt(enchant, 0))
    else:
        item = ItemName(1, name, 0)
    return item
    
def _addTierNickname(name: ItemName, item: dict) -> None:
    item["CommonNames"].append(f"T{name.tier}.{name.enchant} {name.name}")
    if(name.enchant == 0):
        item["CommonNames"].append(f"T{name.tier} {name.name}")

def _replaceLongTierName(name: ItemName, item: dict) -> None:
    try:
        longName = item["LocalizedNames"]["EN-US"]
        fields = longName.split()
        if fields[0] in TIER_LONG_NAMES:
            short = f"T{name.tier}.{name.enchant}"
            item["CommonNames"].append(" ".join([short] + fields[1:]))
            if name.enchant == 0:
                short = f"T{name.tier}"
                item["CommonNames"].append(" ".join([short] + fields[1:]))
    except TypeError:
        # No localized name for this item, we skip.
        pass

def _replaceLongEnchantName(name: ItemName, item:dict) -> None:
    try:
        longName = item["LocalizedNames"]["EN-US"]
        fields = longName.split()
        if fields[0] in ENC_LONG_NAMES:
            short = f"T{name.tier}.{name.enchant}"
            item["CommonNames"].append(" ".join([short] + fields[1:]))
            if fields[1] in RESOURCE_NAMES:
                item["CommonNames"].append(" ".join([short] + fields[2:]))
            if name.enchant == 0:
                short = f"T{name.tier}"
                item["CommonNames"].append(" ".join([short] + fields[1:]))
                if fields[1] in RESOURCE_NAMES:
                    item["CommonNames"].append(" ".join([short] + fields[2:]))
    except TypeError:
        # No localized name for this item, we skip.
        pass

def main():
    rawData = _getItemData()
    for item in rawData:
        item["CommonNames"] = []

        name = _convertItem(item["UniqueName"])

        _addTierNickname(name, item)
        _replaceLongTierName(name, item)
        _replaceLongEnchantName(name, item)
    with open("items.json" ,"w") as out:
        json.dump(rawData, out)

def getItemsList() -> dict:
    """
    When requesting data, will check if it exists locally.
    If not, will fetch and add common names
    """
    if not path.exists("items.json"):
        main()
    with open("items.json", "r") as infile:
        return json.load(infile)


if __name__ == "__main__":
    main()