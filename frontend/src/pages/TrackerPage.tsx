import { Box, Chip, Paper, Stack, Typography } from "@mui/material";

export const STATUSES = [
  "SAVED", "INTERESTED", "RESUME_GENERATED", "APPLIED", "RECRUITER_CONTACTED",
  "OA_RECEIVED", "INTERVIEW_SCHEDULED", "REJECTED", "OFFER", "ACCEPTED", "DECLINED",
] as const;

export default function TrackerPage() {
  return (
    <>
      <Typography variant="h5" gutterBottom>
        Application tracker
      </Typography>
      <Box sx={{ overflowX: "auto", pb: 2 }}>
        <Stack direction="row" spacing={2} sx={{ minWidth: 1400 }}>
          {STATUSES.map((status) => (
            <Paper key={status} variant="outlined" sx={{ width: 200, p: 1.5, flexShrink: 0 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="subtitle2">
                  {status.replaceAll("_", " ").toLowerCase()}
                </Typography>
                <Chip label={0} size="small" />
              </Stack>
              <Typography variant="caption" color="text.secondary">
                Cards land in Phase 9.
              </Typography>
            </Paper>
          ))}
        </Stack>
      </Box>
    </>
  );
}
