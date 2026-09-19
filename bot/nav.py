"""Navigation stack and context management for FSM-based navigation."""

from __future__ import annotations

from typing import Self

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state


class NavState(StatesGroup):
    """Navigation states for main screens."""

    home = State()
    status = State()
    ping = State()
    echo = State()
    help_screen = State()
    monitor = State()
    cpu = State()
    memory = State()
    network = State()
    disk = State()
    processes = State()


class NavStack:
    """Thread-safe navigation stack for back button support."""

    def __init__(self, initial: str | None = None):
        self._stack: list[str] = [initial] if initial else []

    def push(self, screen: str) -> None:
        """Push a new screen onto the stack."""
        self._stack.append(screen)

    def pop(self) -> str | None:
        """Pop and return the previous screen. Returns None if empty."""
        if len(self._stack) > 1:
            return self._stack.pop()
        return None

    def current(self) -> str | None:
        """Get the current (top) screen."""
        return self._stack[-1] if self._stack else None

    def reset(self) -> None:
        """Reset stack to just ['home']."""
        self._stack = ["home"]

    def is_at_root(self) -> bool:
        """Check if at the home screen."""
        return len(self._stack) <= 1


class NavContext:
    """Persistent navigation context stored in FSM."""

    def __init__(self, stack: list[str] | None = None):
        self.stack: list[str] = stack or ["home"]

    def current(self) -> str | None:
        """Get current screen from stack."""
        return self.stack[-1] if self.stack else None

    @classmethod
    def from_fsm(cls, context: FSMContext) -> Self:
        """Load NavContext from FSM storage."""
        data = context.get_data()
        stack = data.get("nav_stack", ["home"])
        return cls(stack=stack)

    def save_to_fsm(self, context: FSMContext) -> None:
        """Save current NavContext to FSM storage."""
        import asyncio

        asyncio.create_task(context.update_data(nav_stack=self.stack))

    def go_home(self) -> str:
        """Navigate to home, replacing stack."""
        self.stack = ["home"]
        return "home"

    def go_back(self) -> str | None:
        """Navigate back, returning the previous screen."""
        if len(self.stack) > 1:
            self.stack.pop()
            return self.stack[-1]
        return None

    def go_to(self, screen: str, push: bool = True) -> str:
        """Navigate to a screen, optionally pushing onto stack."""
        if push and self.stack and self.stack[-1] != "home":
            self.stack.append(screen)
        elif push:
            self.stack = [self.stack[0] if self.stack else "home", screen]
        else:
            self.stack[-1] = screen
        return screen

    def cancel(self) -> str:
        """Cancel current operation, go to home."""
        self.stack = ["home"]
        return "home"


# Button to handler mapping (Reply Keyboard text -> action)
NAV_BUTTONS = {
    "🏠 Home": "go_home",
    "← Back": "go_back",
    "✖ Cancel": "cancel",
}

# Legacy state constants for backward compatibility
ROOT_STATE = default_state
HOME_STATE = NavState.home
STATUS_STATE = NavState.status
PING_STATE = NavState.ping
ECHO_STATE = NavState.echo
HELP_STATE = NavState.help_screen
