"""
Shared domain exception types. Every atlas.core validation failure raises one of
these (never a bare ValueError/TypeError) so calling code can catch "this is a
domain rule violation" distinctly from a genuine programming bug.
"""


class AtlasDomainError(Exception):
    """Base type for every domain-rule violation raised anywhere under atlas.core.
    Catch this specifically when you want to handle "the input violated a domain
    rule" without also swallowing unrelated bugs."""


class OffTickError(AtlasDomainError):
    """Raised when a Price is constructed from a value that does not sit on the
    instrument's tick grid (within floating-point tolerance)."""


class InvalidSymbolError(AtlasDomainError):
    """Raised when a Symbol is constructed from a blank or otherwise invalid
    ticker string."""


class NaiveDatetimeError(AtlasDomainError):
    """Raised when a timezone-naive datetime is passed somewhere this system
    requires an explicit, timezone-aware UTC value. See atlas.core.time."""
