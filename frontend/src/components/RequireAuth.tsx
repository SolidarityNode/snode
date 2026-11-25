import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import { useSession } from "../app/session";
import { useT } from "../i18n/context";

export function RequireAuth({ children, admin = false }: { children: ReactNode; admin?: boolean }) {
  const { user, loading } = useSession();
  const { t } = useT();
  const location = useLocation();
  if (loading) return <p role="status">{t("common.loading")}</p>;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (admin && user.role !== "admin") return <p role="alert">{t("common.admin_only")}</p>;
  return <>{children}</>;
}
