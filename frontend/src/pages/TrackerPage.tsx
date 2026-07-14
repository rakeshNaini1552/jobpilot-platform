import {
  Box, Card, CardContent, Chip, Link, MenuItem, Paper, Select, Stack, Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

export const STATUSES = [
  "SAVED", "INTERESTED", "RESUME_GENERATED", "APPLIED", "RECRUITER_CONTACTED",
  "OA_RECEIVED", "INTERVIEW_SCHEDULED", "REJECTED", "OFFER", "ACCEPTED", "DECLINED",
] as const;
type Status = (typeof STATUSES)[number];

const label = (s: string) => s.replaceAll("_", " ").toLowerCase();

export default function TrackerPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["applications"],
    queryFn: async () =>
      (await api.GET("/api/v1/applications", { params: { query: { size: 100 } } })).data,
  });

  const changeStatus = useMutation({
    mutationFn: async ({ id, to }: { id: string; to: Status }) =>
      api.POST("/api/v1/applications/{application_id}/status", {
        params: { path: { application_id: id } },
        body: { to_status: to },
      }),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  const items = data?.items ?? [];
  const byStatus = (status: Status) => items.filter((a) => a.status === status);

  return (
    <>
      <Typography variant="h5" gutterBottom>
        Application tracker
      </Typography>
      {isLoading && <Typography color="text.secondary">Loading…</Typography>}
      <Box sx={{ overflowX: "auto", pb: 2 }}>
        <Stack direction="row" spacing={2} sx={{ minWidth: 1500 }}>
          {STATUSES.map((status) => {
            const cards = byStatus(status);
            return (
              <Paper key={status} variant="outlined"
                     sx={{ width: 230, p: 1.5, flexShrink: 0, bgcolor: "#fafbfc" }}>
                <Stack direction="row" justifyContent="space-between"
                       alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="subtitle2">{label(status)}</Typography>
                  <Chip label={cards.length} size="small" />
                </Stack>
                <Stack spacing={1}>
                  {cards.map((a) => (
                    <Card key={a.id} variant="outlined">
                      <CardContent sx={{ p: 1.5, "&:last-child": { pb: 1.5 } }}>
                        <Link href={a.job?.url ?? "#"} target="_blank"
                              rel="noreferrer" underline="hover"
                              variant="body2" fontWeight={500}>
                          {a.job?.title}
                        </Link>
                        <Typography variant="caption" color="text.secondary"
                                    display="block" sx={{ mb: 1 }}>
                          {a.job?.location_text || a.job?.connector_id}
                        </Typography>
                        <Select
                          size="small" fullWidth value={a.status}
                          inputProps={{ "aria-label": `status of ${a.job?.title}` }}
                          onChange={(e) => changeStatus.mutate(
                            { id: a.id!, to: e.target.value as Status })}
                          sx={{ fontSize: 12 }}
                        >
                          {STATUSES.map((s) => (
                            <MenuItem key={s} value={s} sx={{ fontSize: 12 }}>
                              {label(s)}
                            </MenuItem>
                          ))}
                        </Select>
                      </CardContent>
                    </Card>
                  ))}
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      </Box>
    </>
  );
}
