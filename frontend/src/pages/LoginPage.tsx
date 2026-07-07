import { AutoAwesome } from "@mui/icons-material";
import {
  Alert, Box, Button, Card, CardContent, Stack, TextField, Typography,
} from "@mui/material";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error: err } = await api.POST("/auth/login", {
      body: { email, password },
    });
    setBusy(false);
    if (err || !data) {
      setError((err as { detail?: string })?.detail ?? "Login failed");
      return;
    }
    setSession(data.access_token, data.refresh_token, {
      id: data.user?.id ?? "",
      email: data.user?.email ?? email,
      full_name: data.user?.full_name ?? "",
      role: (data.user?.role as "USER" | "ADMIN") ?? "USER",
    });
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/";
    navigate(from, { replace: true });
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
      <Card sx={{ width: 380 }}>
        <CardContent>
          <Stack component="form" onSubmit={submit} spacing={2} sx={{ p: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <AutoAwesome color="primary" />
              <Typography variant="h5">Sign in to JobPilot</Typography>
            </Stack>
            {error && <Alert severity="error">{error}</Alert>}
            <TextField
              label="Email" type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              label="Password" type="password" required value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" variant="contained" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
