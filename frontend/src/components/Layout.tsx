import { NavLink, Outlet } from "react-router";

export function Layout() {
  return (
    <div className="layout">
      <header className="layout__header">
        <h1>SolidarityNode</h1>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Home
          </NavLink>
          <NavLink to="/health">Health</NavLink>
        </nav>
      </header>
      <main className="layout__main">
        <Outlet />
      </main>
      <footer className="layout__footer">AGPL-3.0 · synthetic data only</footer>
    </div>
  );
}
