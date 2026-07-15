import { AutoAwesome } from "@mui/icons-material";
import {
  Alert, Box, Button, Card, CardContent, Link, Stack, TextField, Typography,
} from "@mui/material";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAuthStore, type SessionUser } from "@/stores/auth";

export default function LoginPage() {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);
  const navigate = useNavigate();
  const location = useLocation();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const { data, error: err } =
      mode === "login"
        ? await api.POST("/api/v1/auth/login", { body: { email, password } })
        : await api.POST("/api/v1/auth/register", {
            body: { email, password, full_name: fullName },
          });
    setBusy(false);
    if (err || !data) {
      const problem = err as { detail?: string; title?: string } | undefined;
      setError(problem?.detail || problem?.title ||
        (mode === "login" ? "Login failed" : "Registration failed"));
      return;
    }
    setSession(data.access_token, data.refresh_token, data.user as SessionUser);
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? "/";
    navigate(from, { replace: true });
  };

  const registering = mode === "register";
  return (
    <Box sx={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
      <Card sx={{ width: 380 }}>
        <CardContent>
          <Stack component="form" onSubmit={submit} spacing={2} sx={{ p: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center">
              <AutoAwesome color="primary" />
              <Typography variant="h5">
                {registering ? "Create your account" : "Sign in to JobPilot"}
              </Typography>
            </Stack>
            {registering && (
              <Alert severity="info" sx={{ py: 0 }}>
                The first account becomes the admin.
              </Alert>
            )}
            {error && <Alert severity="error">{error}</Alert>}
            {registering && (
              <TextField
                label="Full name" required value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            )}
            <TextField
              label="Email" type="email" required value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              label="Password" type="password" required value={password}
              helperText={registering ? "At least 10 characters" : undefined}
              slotProps={{ htmlInput: { minLength: registering ? 10 : undefined } }}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" variant="contained" disabled={busy}>
              {busy ? "Working…" : registering ? "Create account" : "Sign in"}
            </Button>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              {registering ? "Already have an account? " : "New here? "}
              <Link component="button" type="button"
                    onClick={() => { setMode(registering ? "login" : "register"); setError(null); }}>
                {registering ? "Sign in" : "Create an account"}
              </Link>
            </Typography>
          </Stack>
        </CardContent>
      </Card>
    </Box>
  );
}
