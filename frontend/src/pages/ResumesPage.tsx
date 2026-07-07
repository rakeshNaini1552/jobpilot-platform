import { Paper, Typography } from "@mui/material";

export default function ResumesPage() {
  return (
    <>
      <Typography variant="h5" gutterBottom>
        Resumes
      </Typography>
      <Paper variant="outlined" sx={{ p: 3 }}>
        <Typography color="text.secondary">Upload, parsing, ATS analysis, and tailoring land in Phases 7-8.</Typography>
      </Paper>
    </>
  );
}
