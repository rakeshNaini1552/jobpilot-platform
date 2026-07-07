import { Paper, Typography } from "@mui/material";

export default function JobsPage() {
  return (
    <>
      <Typography variant="h5" gutterBottom>
        Jobs
      </Typography>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary">Search filters, ranked results, and CSV export land in Phase 7.</Typography>
      </Paper>
    </>
  );
}
