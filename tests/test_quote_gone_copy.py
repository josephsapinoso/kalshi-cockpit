"""The refusal for a quote Kalshi no longer has claims no lifetime (town hall #415).

It said a maker price "lives for a few seconds" and that this one "expired
before the tap landed". Neither was measured, and `not_found` also covers a
quote its maker withdrew. What is known is what Kalshi said and that nothing
was placed.
"""

from backend.combo_rfq import _venue_refusal_words


class _Refused(Exception):
    def __init__(self, status_code, body):
        super().__init__(body)
        self.status_code = status_code
        self.body = body


class TestAGoneQuoteSaysOnlyWhatKalshiSaid:
    def test_not_found_names_both_causes_and_no_lifetime(self):
        words = _venue_refusal_words(_Refused(404, '{"code":"not_found"}'))

        assert words.startswith("Kalshi says that quote is no longer available.")
        assert "expired or been withdrawn" in words
        assert "Nothing was placed and nothing was charged" in words
        assert "few seconds" not in words
        assert "before the tap landed" not in words

    def test_expired_reads_the_same(self):
        words = _venue_refusal_words(_Refused(409, '{"code":"quote_expired"}'))

        assert "no longer available" in words
        assert "few seconds" not in words
