import { ThemeProvider } from "@mui/material";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";
import { useAuthStore } from "./stores/auth";
import { theme } from "./theme";

function renderAt(path: string) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ThemeProvider theme={theme}>
        <MemoryRouter initialEntries={[path]}>
          <App />
        </MemoryRouter>
      </ThemeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => useAuthStore.getState().logout());

test("unauthenticated users are redirected to login", () => {
  renderAt("/");
  expect(screen.getByText("Sign in to JobPilot")).toBeInTheDocument();
});

test("authenticated users see the dashboard shell", () => {
  useAuthStore.getState().setSession("token", "refresh", {
    id: "1", email: "r@x.com", full_name: "Rakesh", role: "USER",
  });
  renderAt("/");
  expect(screen.getByRole("heading", { name: "Dashboard" })).toBeInTheDocument();
  expect(screen.getByText("Jobs found")).toBeInTheDocument();
  expect(screen.queryByText("Admin")).not.toBeInTheDocument();
});

test("admin nav appears only for ADMIN role", () => {
  useAuthStore.getState().setSession("token", "refresh", {
    id: "1", email: "r@x.com", full_name: "Rakesh", role: "ADMIN",
  });
  renderAt("/");
  expect(screen.getByText("Admin")).toBeInTheDocument();
});

test("tracker shows all 11 pipeline columns", () => {
  useAuthStore.getState().setSession("token", "refresh", {
    id: "1", email: "r@x.com", full_name: "Rakesh", role: "USER",
  });
  renderAt("/tracker");
  expect(screen.getByText("Application tracker")).toBeInTheDocument();
  expect(screen.getByText("interview scheduled")).toBeInTheDocument();
  expect(screen.getByText("offer")).toBeInTheDocument();
});
