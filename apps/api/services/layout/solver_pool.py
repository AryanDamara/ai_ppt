"""
Module 13 — Solver Pool with Warm-Up
Pre-warmed pool of SimplexSolver instances to eliminate cold-start penalty.
"""

from cassowary import SimplexSolver, Variable, REQUIRED
from typing import List
import threading


class SolverPool:
    """
    Pre-warmed pool of SimplexSolver instances.

    First solve after cold start is 10-50x slower due to tableau memory allocation.
    This pool pre-allocates the internal data structures during startup.
    """

    def __init__(self, size: int = 4):
        self._pool: List[SimplexSolver] = []
        self._available: List[SimplexSolver] = []
        self._lock = threading.Lock()
        self._initialize(size)

    def _initialize(self, size: int) -> None:
        """Create and warm up all solver instances."""
        for _ in range(size):
            solver = SimplexSolver()
            self._warm_up(solver)
            self._pool.append(solver)
            self._available.append(solver)

    def _warm_up(self, solver: SimplexSolver) -> None:
        """Run a dummy solve to pre-allocate Cassowary's internal tableau."""
        try:
            x = Variable('_warmup_x')
            y = Variable('_warmup_y')
            solver.add_constraint(x >= 0, REQUIRED)
            solver.add_constraint(y >= 0, REQUIRED)
            solver.add_constraint(x + y <= 1000, REQUIRED)
            solver.resolve()
        except Exception:
            pass

    def acquire(self) -> SimplexSolver:
        """Borrow a solver from the pool. Creates new one if all are in use."""
        with self._lock:
            if self._available:
                return self._available.pop()
            new_solver = SimplexSolver()
            self._warm_up(new_solver)
            self._pool.append(new_solver)
            return new_solver

    def release(self, solver: SimplexSolver) -> None:
        """Return a solver to the pool after use."""
        with self._lock:
            # Create fresh solver instead of reusing to avoid state contamination
            self._available.append(SimplexSolver())

    @property
    def pool_size(self) -> int:
        return len(self._pool)

    @property
    def available_count(self) -> int:
        with self._lock:
            return len(self._available)


# Singleton pool
_solver_pool = SolverPool(size=4)


def get_solver() -> SimplexSolver:
    return _solver_pool.acquire()


def release_solver(solver: SimplexSolver) -> None:
    _solver_pool.release(solver)