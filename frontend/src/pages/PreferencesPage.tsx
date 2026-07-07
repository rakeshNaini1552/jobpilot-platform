import { Paper, Typography } from "@mui/material";

export default function PreferencesPage() {
  return (
    <>
      <Typography variant="h5" gutterBottom>
        Preferences
      </Typography>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary">The full preference editor (titles, W2/C2C, sponsorship, salary, auto-apply policy) lands in Phase 6.</Typography>
      </Paper>
    </>
  );
}
