import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { api, unwrap, type Schemas } from "../api/client";
import { SessionContext } from "./session";

export function SessionProvider({ children }: { children: ReactNode }) {
  const [config, setConfig] = useState<Schemas["AppConfigOut"] | null>(null);
  const [user, setUser] = useState<Schemas["UserOut"] | null>(null);
  const [dv, setDv] = useState<Schemas["DataVersionOut"] | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshDataVersion = useCallback(async () => {
    try {
      setDv(await unwrap(api.GET("/data-versions/active")));
    } catch {
      setDv(null);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const cfg = await unwrap(api.GET("/config"));
        if (!cancelled) setConfig(cfg);
      } catch {
        /* backend down: pages show their own errors */
      }
      try {
        const me = await unwrap(api.GET("/auth/me"));
        if (!cancelled) {
          setUser(me);
          await refreshDataVersion();
        }
      } catch {
        if (!cancelled) setUser(null);
      }
      if (!cancelled) setLoading(false);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [refreshDataVersion]);

  const login = useCallback(
    async (username: string, password: string) => {
      const me = await unwrap(api.POST("/auth/login", { body: { username, password } }));
      setUser(me);
      await refreshDataVersion();
    },
    [refreshDataVersion],
  );

  const logout = useCallback(async () => {
    await api.POST("/auth/logout");
    setUser(null);
    setDv(null);
  }, []);

  const value = useMemo(
    () => ({
      config,
      user,
      activeDataVersion: dv,
      loading,
      login,
      logout,
      refreshDataVersion,
    }),
    [config, user, dv, loading, login, logout, refreshDataVersion],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}
