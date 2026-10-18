"""Shared label definitions (GRADING_CONTRACT.md common labels) plus our worked examples.

One source of truth: the Jev questions, the verifier prompt, the validator and the README all
read from here. Examples are written by us for illustration; none are golden-set reviews.
"""

LABELS_VERSION = "labels-v1"

TOPICS = {
    "access": "Login, signup, password or account access problems (e.g. 'can't log in', 'account hacked', 'logged out every day').",
    "usability": "Navigation, controls, layout, UI changes, queue/playlist management, ad interruptions (e.g. 'new home screen is confusing', 'too many ads between songs').",
    "playback": "Playback failure, crashes, freezing, lag, songs stopping or skipping by themselves, connection failures, audio quality, battery/data/storage use.",
    "downloads": "Downloading songs, saved music, offline listening, downloads disappearing.",
    "catalog": "Missing songs or artists, removed content, search and discovery, recommendations, lyrics availability, podcasts content.",
    "billing": "Price, charges, subscriptions, refunds, paywalls, premium entitlement; controls explicitly limited to premium (e.g. 'can't pick songs without premium', 'only 6 skips') go here.",
    "support": "Contacting customer support and the support response (e.g. 'support never replied', 'no way to reach a human').",
    "other": "General praise or general criticism with no specific feature, unrelated content, politics/boycott slogans, or no supported specific topic.",
}

TOPIC_RULES = (
    "Classify the review text itself, never the star rating. If several problems are reported, choose the one with the "
    "highest severity; on a tie, the first specific problem mentioned. For a positive review, choose the first specific "
    "praised feature; general praise is 'other'. Mentioning a paid plan alone does not make the topic billing: a "
    "subscription failing to activate is billing, but music crashing for a paying customer is playback."
)

INTENTS = {
    "cancellation": "Explicitly leaving, uninstalling, cancelling a subscription, switching to a competitor, or threatening to do so.",
    "complaint": "A negative experience, including mixed praise and criticism, and generic 'bad app' / 'worst app'.",
    "request": "Asks for a change or new feature without reporting a failure.",
    "praise": "Positive feedback with no complaint.",
    "unclear": "Bare boycott slogans, unrelated or meaningless text, or text whose intent cannot be determined.",
}

INTENT_RULES = (
    "Use this precedence: cancellation > complaint > request > praise > unclear. Pick cancellation whenever the reviewer "
    "explicitly leaves, uninstalls, cancels or threatens to, even if they also complain. Bare boycott slogans and "
    "unrelated text are unclear unless a product complaint or a personal departure is expressed."
)

SEVERITY = {
    1: "No reported problem: praise, neutral or unclear content, or a pure feature request.",
    2: "Dislike, generic criticism, minor annoyance or cosmetic issue; no supported loss of function.",
    3: "A degraded or restricted function; some use or a workaround remains (e.g. ads too frequent, shuffle forced, lag).",
    4: "A clearly blocked core task: cannot log in, cannot play music, app will not open, downloads unusable.",
    5: "Explicit serious financial, privacy or data harm (e.g. charged after cancelling, account stolen, library deleted). An expensive plan, a crash or angry language alone is not enough.",
}

SEVERITY_RULES = (
    "Rate the reported impact, not the tone. Stars, angry language or cancellation intent alone do not raise severity. "
    "If the impact is not described, do not invent it."
)

SENTIMENT_LEVELS = [
    "Very negative: angry, hostile or strongly dissatisfied",
    "Negative: dissatisfied or disappointed",
    "Neutral or mixed: balanced praise and criticism, or no emotional tone",
    "Positive: satisfied",
    "Very positive: enthusiastic or delighted",
]

# Worked examples (illustrative, written for this project) showing how the shared rules were applied.
EXAMPLES = [
    {"text": "Downloaded songs stop playing when I go offline.", "topic": "downloads", "intent": "complaint", "severity": 4,
     "why": "Offline playback of saved music is the core task and it is blocked."},
    {"text": "Love it, but please add a sleep timer for podcasts", "topic": "other", "intent": "request", "severity": 1,
     "why": "Mixed praise plus a wish with no failure: request beats praise; no specific problem so severity 1. Topic other because a sleep timer is a new feature, not one of the defined areas failing."},
    {"text": "Too many ads, one after every song. Uninstalling.", "topic": "usability", "intent": "cancellation", "severity": 3,
     "why": "Ad interruptions are usability; the reviewer explicitly leaves (cancellation wins); music still plays, so degraded (3)."},
    {"text": "I can't even choose which song to play unless I pay for premium", "topic": "billing", "intent": "complaint", "severity": 3,
     "why": "An explicitly premium-only control is billing; function is restricted, not blocked."},
    {"text": "Charged twice this month and support won't answer", "topic": "billing", "intent": "complaint", "severity": 5,
     "why": "Explicit financial harm (5) outranks the support problem, so the topic follows the highest-severity problem."},
    {"text": "App keeps crashing on startup since the update", "topic": "playback", "intent": "complaint", "severity": 4,
     "why": "Crashes are playback; the app cannot be used at all, so a core task is blocked."},
    {"text": "Worst app", "topic": "other", "intent": "complaint", "severity": 2,
     "why": "Generic criticism: complaint with no specific defect, severity 2."},
    {"text": "Boycott Spotify!!", "topic": "other", "intent": "unclear", "severity": 1,
     "why": "Bare boycott slogan with no product complaint or personal departure."},
    {"text": "Great app, the Discover Weekly playlists are spot on", "topic": "catalog", "intent": "praise", "severity": 1,
     "why": "First specific praised feature is recommendations (catalog)."},
    {"text": "Logged me out and now says my password is wrong, can't get in", "topic": "access", "intent": "complaint", "severity": 4,
     "why": "Account access is blocked."},
]


def sentiment_from_score(score):
    """Jev Score position 0..4 -> sentiment -1..1 (score / 2 - 1), clamped and rounded for export."""
    return round(max(-1.0, min(1.0, score / 2 - 1)), 3)
