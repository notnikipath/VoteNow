from shared.votenow_common import average_rating, forecast_turnout, parallel_write_plan, sentiment_label


def test_average_rating() -> None:
    assert average_rating([4, 8, 10]) == 7.33


def test_forecast_turnout() -> None:
    assert forecast_turnout(100, elapsed_minutes=10, total_duration_minutes=60) >= 100


def test_parallel_write_plan() -> None:
    plan = parallel_write_plan(10000, 8)
    assert plan["writers"] >= 2
    assert plan["batch_size"] >= 50


def test_sentiment_label() -> None:
    assert sentiment_label("excellent clear great") == "positive"
