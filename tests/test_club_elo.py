import unittest

from jingcai.models.club_elo import ClubEloModel


MATCHES = [
    {"date": "2024-01-02", "home": "A", "away": "B", "home_goals": 2, "away_goals": 0,
     "home_association": "strong", "away_association": "weak"},
    {"date": "2024-02-02", "home": "B", "away": "A", "home_goals": 1, "away_goals": 1,
     "home_association": "weak", "away_association": "strong"},
]


def provider(match, team, association):
    return {"strong": 1600.0, "weak": 1400.0}.get(association)


class ClubEloTests(unittest.TestCase):
 def test_new_club_uses_shrunk_point_in_time_association_prior(self):
    model = ClubEloModel(home_advantage=0, prior_weight=0.5).fit(MATCHES, provider)
    home_rate, away_rate = model.expected_goals(
        "New Strong", "New Weak", home_association="strong", away_association="weak",
        association_priors={"strong": 1700.0, "weak": 1300.0},
    )
    self.assertGreater(home_rate, away_rate)
    full = ClubEloModel(home_advantage=0, prior_weight=1.0).fit(MATCHES, provider)
    full_home, full_away = full.expected_goals(
        "New Strong", "New Weak", home_association="strong", away_association="weak",
        association_priors={"strong": 1700.0, "weak": 1300.0},
    )
    self.assertLess(home_rate / away_rate, full_home / full_away)
    # Prediction-time priors do not mutate learned state.
    self.assertNotIn("New Strong", model.ratings)


 def test_fit_sorts_strictly_by_time_and_prior_is_read_at_each_match(self):
    seen = []
    def recording_provider(match, team, association):
        seen.append((match["date"], team))
        return provider(match, team, association)

    model = ClubEloModel().fit(reversed(MATCHES), recording_provider)
    self.assertEqual([row[0] for row in model.history], sorted(row[0] for row in model.history))
    self.assertEqual("2024-01-02", seen[0][0])
    # Existing teams retain learned global Elo; a later supplied prior cannot reset them.
    after_first = ClubEloModel().fit(MATCHES[:1], provider)
    self.assertAlmostEqual(after_first.ratings["B"], model.history[1][3])


 def test_score_matrix_and_1x2_are_normalized(self):
    model = ClubEloModel().fit(MATCHES, provider)
    matrix = model.predict_score_matrix("A", "B", max_goals=7)
    one_x_two = model.predict_1x2("A", "B", max_goals=7)
    self.assertAlmostEqual(1.0, sum(map(sum, matrix)))
    self.assertAlmostEqual(1.0, sum(one_x_two.values()))
    self.assertTrue(all(value >= 0 for value in one_x_two.values()))


if __name__ == "__main__":
    unittest.main()
