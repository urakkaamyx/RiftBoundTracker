import sys
sys.path.insert(0, "src")
from riftkeep_rules.deck_construction import detect_deck_obligations
from riftkeep_rules.player_language import normalize_player_language

LEGITIMATE = [
    "Can I play more than one Legend in my deck?",
    "Can I have two Legends in my deck?",
    "Can I run two Champion Legends?",
    "Can my deck have multiple Legends?",
    "Can I use more than one Champion Legend?",
    "How many Champion Legends can my deck contain?",
    "Can I put 2 Legends in a deck?",
    "Is more than one Champion Legend allowed?",
    "How many Legends do I need?",
    "Can I have a 39-card Main Deck?",
    "Can I use only 35 cards?",
    "Can I have more than 40 cards?",
    "How many cards does my Main Deck need?",
    "Can I run four copies of the same card?",
    "Can I have three copies plus my Chosen Champion?",
    "Does my Chosen Champion count toward the copy limit?",
    "Can I run three Yasuo, Remorseful and three Yasuo, Windrider?",
    "Can I use four Signature cards?",
    "Can I use Signature cards from another Champion?",
    "Can a Signature unit be my Chosen Champion?",
    "Can I use 13 runes?",
    "Can I use 11 runes?",
    "How many runes do I need?",
    "Can my Rune Deck contain a rune outside my Domain Identity?",
    "How many Battlefields do I need?",
    "Can I use two copies of the same Battlefield?",
]

FAILING = [
    "I'm in a game and this rules situation comes up under Silver Rule: The situation involves this rule concept: Non-Board zones corresponding to a player include Main Deck, Rune Deck, Trash, Hand, Chosen Champion zone, and Banishment. What does the rule require?",
    "What happens here under the Deck Construction rules: The situation involves this rule concept: This is placed in the Legend Zone at the start of the game.",
    "A player at my table is asking about Deck Construction. The situation involves this rule concept: A Main Deck of at least 40 cards: A Chosen Champion Unit, as well as Units, Gear, and Spells What's the correct ruling?",
    "Can you settle this Deck Construction rules question: The situation involves this rule concept: This will be placed in the Champion Zone at the start of the game.",
]

print("=== LEGITIMATE (must keep matching correctly) ===")
for q in LEGITIMATE:
    norm = normalize_player_language(q)["text"]
    obs = detect_deck_obligations(norm.lower())
    print(f"{obs} | {q}")

print("\n=== FAILING corpus cases (should NOT match, or should match something sensible) ===")
for q in FAILING:
    norm = normalize_player_language(q)["text"]
    obs = detect_deck_obligations(norm.lower())
    print(f"{obs} | {q[:100]}")
