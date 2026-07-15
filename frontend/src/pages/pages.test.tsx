/** Page-level tests with the API client mocked at the module boundary
 * (openapi-fetch binds globalThis.fetch at import time, so stubbing fetch
 * per-test is too late — mock the client instead). */
import { ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, type Mock } from "vitest";
import { api } from "@/api/client";
import DashboardPage from "./DashboardPage";
import JobsPage from "./JobsPage";
import { theme } from "../theme";

vi.mock("@/api/client", () => ({
  api: { GET: vi.fn(), POST: vi.fn() },
}));

function renderPage(page: React.ReactElement) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ThemeProvider theme={theme}>
        <MemoryRouter>{page}</MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

test("dashboard renders KPIs and suggestions from the API payload", async () => {
  (api.GET as Mock).mockResolvedValue({
    data: {
      jobs_found: 12, jobs_applied: 4, interviews: 2, rejections: 1, offers: 1,
      success_rate: 25.0, recruiter_response_rate: 75.0,
      applications_by_week: [{ week: "2026-07-13", count: 4 }],
      applications_by_company: [], match_score_distribution: [],
      salary_distribution: [], funnel: [],
      ai_suggestions: ["'Kubernetes' appears in 3 matched jobs but not on your resume."],
      top_matches: [{ title: "Senior Java Developer", url: "https://x", score: 84 }],
    },
  });
  renderPage(<DashboardPage />);
  await waitFor(() => expect(screen.getByText("12")).toBeInTheDocument());
  expect(screen.getByText("Senior Java Developer")).toBeInTheDocument();
  expect(screen.getByText(/Kubernetes/)).toBeInTheDocument();
});

test("jobs page renders rows with W2/C2C chips", async () => {
  (api.GET as Mock).mockResolvedValue({
    data: {
      items: [{
        id: "1", title: "Full Stack Java Developer", connector_id: "dice",
        url: "https://dice.com/1", location_text: "Dallas, TX",
        workplace: "HYBRID", employment: "CONTRACT", arrangement: "C2C",
        salary_min: null, salary_max: 130000, salary_currency: "USD",
        posted_at: null,
      }],
      page: 1, size: 50, total: 1,
    },
  });
  renderPage(<JobsPage />);
  await waitFor(() =>
    expect(screen.getByText("Full Stack Java Developer")).toBeInTheDocument());
  expect(screen.getByText("C2C")).toBeInTheDocument();
  expect(screen.getByText("$130k")).toBeInTheDocument();
});

test("jobs page shows the empty state", async () => {
  (api.GET as Mock).mockResolvedValue({
    data: { items: [], page: 1, size: 50, total: 0 },
  });
  renderPage(<JobsPage />);
  await waitFor(() =>
    expect(screen.getByText(/No jobs yet/)).toBeInTheDocument());
});
