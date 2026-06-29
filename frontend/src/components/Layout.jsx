import { Link, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../auth/AuthContext.jsx";

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          DeepResearch
        </Link>
        <span className="spacer" />
        {user && <span className="who">{user.email}</span>}
        <button className="ghost" onClick={handleLogout}>
          Sign out
        </button>
      </header>
      <Outlet />
    </>
  );
}
