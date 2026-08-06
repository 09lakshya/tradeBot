"""Domain Exceptions for Portfolio Construction & Signal Arbitration Engine."""


class PortfolioConstructionError(Exception):
    """Base domain exception for portfolio construction failures."""
    pass


class InsufficientCapitalError(PortfolioConstructionError):
    """Raised when available cash after reserve requirements is insufficient for allocation."""
    pass


class IncompatibleSignalError(PortfolioConstructionError):
    """Raised when an incoming signal violates point-in-time timestamp constraints or is malformed."""
    pass


class InvalidPortfolioConfigError(PortfolioConstructionError):
    """Raised when portfolio optimization constraints or policy parameters are mathematically infeasible."""
    pass


class OptimizationConvergenceError(PortfolioConstructionError):
    """Raised when the numerical optimization routine fails to converge within tolerances."""
    pass


class SizingError(PortfolioConstructionError):
    """Raised when position sizing produces non-positive or unquantizable lots."""
    pass
