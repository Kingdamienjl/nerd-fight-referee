import sys
sys.path.insert(0, "/app/src")
from battlebot.review.auto_repair import fragment_item_reasons
print("season1:", fragment_item_reasons("Season 1", section="weaknesses"))
print("iori:", fragment_item_reasons("Iori can control fire. He can create a bright purple fire from thin air", section="weaknesses"))
print("whitesnake:", fragment_item_reasons("Whitesnake can control them", section="weaknesses"))
print("file:", __import__("battlebot.review.auto_repair", fromlist=["x"]).__file__)
