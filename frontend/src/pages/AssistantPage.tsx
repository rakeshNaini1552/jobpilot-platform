import { Paper, Typography } from "@mui/material";

export default function AssistantPage() {
  return (
    <>
      <Typography variant="h5" gutterBottom>
        Assistant
      </Typography>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary">RAG chat over your jobs, resumes, and applications lands in Phase 8.</Typography>
      </Paper>
    </>
  );
}
