import { ReactNode } from "react";

export type Page = "review" | "legal-qa" | "escalations" | "dashboard";

type LayoutProps = {
  activePage: Page;
  onPageChange: (page: Page) => void;
  children: ReactNode;
};

const pages: Array<{ id: Page; label: string }> = [
  { id: "review", label: "Contract Review" },
  { id: "legal-qa", label: "Legal Q&A" },
  { id: "escalations", label: "Escalations" },
  { id: "dashboard", label: "Dashboard" }
];

export function Layout({ activePage, onPageChange, children }: LayoutProps) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Harvey BMW</div>
        <nav>
          {pages.map((page) => (
            <button
              key={page.id}
              className={activePage === page.id ? "active" : ""}
              onClick={() => onPageChange(page.id)}
            >
              {page.label}
            </button>
          ))}
        </nav>
      </aside>
      <main className="content">{children}</main>
    </div>
  );
}
