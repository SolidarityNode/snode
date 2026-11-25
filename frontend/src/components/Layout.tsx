import { NavLink, Outlet, useNavigate } from "react-router";

import { useSession } from "../app/session";
import { useT, type Lang } from "../i18n/context";
import { MapPatterns } from "../map/MapPatterns";
import { BuildInfo } from "./BuildInfo";
import { label } from "./labels";

export function Layout() {
  const { t, lang, setLang } = useT();
  const { user, logout, activeDataVersion: dv } = useSession();
  const navigate = useNavigate();
  return (
    <div className="layout">
      <a className="skip-link" href="#main">
        {t("nav.skip")}
      </a>
      <MapPatterns />
      <header className="layout__header">
        <h1 className="layout__brand">
          <img src="/brand/logo.svg" alt="" width="56" height="32" />
          SN Kintsugi
        </h1>
        <nav aria-label={t("nav.main")}>
          {user && (
            <>
              <NavLink to="/" end>
                {t("nav.study_area")}
              </NavLink>
              <NavLink to="/scenarios">{t("nav.scenarios")}</NavLink>
              {user.role === "admin" && <NavLink to="/admin">{t("nav.admin")}</NavLink>}
            </>
          )}
          <NavLink to="/health">{t("nav.health")}</NavLink>
        </nav>
        <div className="layout__tools">
          <label>
            {t("nav.language")}{" "}
            <select
              value={lang}
              onChange={(e) => {
                setLang(e.target.value as Lang);
              }}
            >
              <option value="en">English</option>
              <option value="el">Ελληνικά</option>
            </select>
          </label>
          {user && (
            <span>
              {t("nav.signed_in_as", { user: user.username, role: label(t, "role", user.role) })}{" "}
              <button
                type="button"
                onClick={() => {
                  void logout().then(() => navigate("/login"));
                }}
              >
                {t("nav.logout")}
              </button>
            </span>
          )}
        </div>
      </header>
      <main id="main" className="layout__main">
        <Outlet />
      </main>
      <footer className="layout__footer">
        {t("footer.licence")} ·{" "}
        <span data-testid="data-version">
          {dv
            ? t("footer.data_version", { package: dv.package_id, version: dv.version })
            : t("footer.no_data")}
        </span>{" "}
        · <BuildInfo />
      </footer>
    </div>
  );
}
