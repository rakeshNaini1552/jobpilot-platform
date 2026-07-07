import { Paper, Typography } from "@mui/material";

export default function AdminPage() {
  return (
    <>
      <Typography variant="h5" gutterBottom>
        Admin
      </Typography>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary">AI providers, connectors, prompts, schedules, and audit log land in Phase 10.</Typography>
      </Paper>
    </>
  );
}
