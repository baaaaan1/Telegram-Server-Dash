"""Tests for navigation stack and context."""

from bot.nav import NavContext, NavStack, NavState


class TestNavStack:
    """Tests for NavStack class."""

    def test_initial_stack_empty(self):
        """Test initial empty stack."""
        stack = NavStack()
        assert stack.current() is None
        assert stack.is_at_root() is True

    def test_initial_stack_with_home(self):
        """Test initial stack with home."""
        stack = NavStack(initial="home")
        assert stack.current() == "home"

    def test_push_and_current(self):
        """Test push adds to stack."""
        stack = NavStack(initial="home")
        stack.push("status")
        assert stack.current() == "status"
        assert stack.is_at_root() is False

    def test_pop_returns_last_element(self):
        """Test pop returns the last element pushed."""
        stack = NavStack(initial="home")
        stack.push("status")
        stack.push("detail")
        assert stack.pop() == "detail"
        assert stack.current() == "status"

    def test_pop_at_root_returns_none(self):
        """Test pop at root returns None."""
        stack = NavStack(initial="home")
        assert stack.pop() is None

    def test_reset_clears_to_home(self):
        """Test reset returns to just home."""
        stack = NavStack(initial="home")
        stack.push("status")
        stack.push("detail")
        stack.reset()
        assert stack.current() == "home"
        assert stack.is_at_root() is True

    def test_is_at_root(self):
        """Test is_at_root detects root state."""
        stack = NavStack(initial="home")
        assert stack.is_at_root() is True
        stack.push("status")
        assert stack.is_at_root() is False


class TestNavContext:
    """Tests for NavContext class."""

    def test_default_stack(self):
        """Test default stack initialization."""
        ctx = NavContext()
        assert ctx.stack == ["home"]

    def test_custom_stack(self):
        """Test custom stack initialization."""
        ctx = NavContext(stack=["home", "status"])
        assert ctx.stack == ["home", "status"]

    def test_go_home(self):
        """Test go_home resets stack."""
        ctx = NavContext(stack=["home", "status", "detail"])
        result = ctx.go_home()
        assert result == "home"
        assert ctx.stack == ["home"]

    def test_go_back(self):
        """Test go_back pops stack."""
        ctx = NavContext(stack=["home", "status"])
        result = ctx.go_back()
        assert result == "home"
        assert ctx.stack == ["home"]

    def test_go_back_at_root(self):
        """Test go_back at root returns None."""
        ctx = NavContext(stack=["home"])
        result = ctx.go_back()
        assert result is None

    def test_go_to_replaces_current(self):
        """Test go_to replaces current screen."""
        ctx = NavContext(stack=["home"])
        result = ctx.go_to("status", push=False)
        assert result == "status"
        assert ctx.current() == "status"

    def test_cancel_clears_stack(self):
        """Test cancel resets to home."""
        ctx = NavContext(stack=["home", "status", "detail"])
        result = ctx.cancel()
        assert result == "home"
        assert ctx.stack == ["home"]


class TestNavState:
    """Tests for NavState StatesGroup."""

    def test_states_exist(self):
        """Test all expected states exist."""
        assert hasattr(NavState, "home")
        assert hasattr(NavState, "status")
        assert hasattr(NavState, "ping")
        assert hasattr(NavState, "echo")
        assert hasattr(NavState, "help_screen")
