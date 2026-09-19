"""Context signals: the consumer's situation (weather, festival, commute) and opt-in personal
options (personal colour, mood, lucky colour), turned into explainable ranking preferences.

Every module here produces `ContextSignal`s (see base.py). The pipeline turns them into ONE
additive term group, "context", itemised per signal so a card can say exactly which situation moved
it and by how much. This is the fifth attribution channel, kept apart from what the user said this
round, last round's feedback, the learned prior and the questionnaire profile.

Rules every signal obeys:
  * a signal only ranks if `affects_ranking` is True; entertainment options (lucky colour) default
    to display-only and must be switched on explicitly by the user;
  * a signal never removes an item -- context is a preference, the user's words are the filter;
  * every signal names its evidence: a measurement, or "opt-in, not measured".
"""

from .base import AttributePref, ContextSignal, DailyForecast  # noqa: F401
