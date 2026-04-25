import { useState } from "react";
import { Layout, Page } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Escalations } from "./pages/Escalations";
import { LegalQA } from "./pages/LegalQA";
import { Review } from "./pages/Review";

export function App() {
  const [page, setPage] = useState<Page>("review");

  return (
    <Layout activePage={page} onPageChange={setPage}>
      {page === "review" && <Review />}
      {page === "legal-qa" && <LegalQA />}
      {page === "escalations" && <Escalations />}
      {page === "dashboard" && <Dashboard />}
    </Layout>
  );
}
