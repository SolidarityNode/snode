import { createContext, useContext } from "react";

import type { Schemas } from "../api/client";

export interface Session {
  config: Schemas["AppConfigOut"] | null;
  user: Schemas["UserOut"] | null;
  activeDataVersion: Schemas["DataVersionOut"] | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshDataVersion: () => Promise<void>;
}

export const SessionContext = createContext<Session>({
  config: null,
  user: null,
  activeDataVersion: null,
  loading: true,
  login: () => Promise.resolve(),
  logout: () => Promise.resolve(),
  refreshDataVersion: () => Promise.resolve(),
});

export function useSession(): Session {
  return useContext(SessionContext);
}

export function canEdit(user: Schemas["UserOut"] | null): boolean {
  return user?.role === "admin" || user?.role === "analyst";
}
