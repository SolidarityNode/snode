import { Route, Routes } from "react-router";

import { Layout } from "./components/Layout";
import { HealthPage } from "./pages/HealthPage";
import { HomePage } from "./pages/HomePage";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<HomePage />} />
        <Route path="health" element={<HealthPage />} />
      </Route>
    </Routes>
  );
}
