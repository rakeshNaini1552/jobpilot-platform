import { PlaylistAdd, Search } from "@mui/icons-material";
import {
  Button, Chip, Link, MenuItem, Paper, Stack, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Typography,
} from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const ARRANGEMENTS = ["", "W2", "C1099", "C2C", "UNSPECIFIED"];
const WORKPLACES = ["", "REMOTE", "HYBRID", "ONSITE"];

export default function JobsPage() {
  const [q, setQ] = useState("");
  const [applied, setApplied] = useState("");
  const [arrangement, setArrangement] = useState("");
  const [workplace, setWorkplace] = useState("");
  const queryClient = useQueryClient();
  const token = useAuthStore((s) => s.accessToken);

  const { data, isLoading } = useQuery({
    queryKey: ["jobs", applied, arrangement, workplace],
    queryFn: async () =>
      (await api.GET("/api/v1/jobs", {
        params: {
          query: {
            size: 50, posted_within_hours: 24 * 30,
            ...(applied ? { q: applied } : {}),
            ...(arrangement ? { arrangement } : {}),
            ...(workplace ? { workplace } : {}),
          },
        },
      })).data,
  });

  const track = useMutation({
    mutationFn: async (jobId: string) =>
      api.POST("/api/v1/applications", { body: { job_id: jobId, status: "SAVED" } }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["applications"] }),
  });

  const runSearch = useMutation({
    mutationFn: async () => api.POST("/api/v1/search-runs", {}),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["jobs"] }),
  });

  const exportCsv = async () => {
    const resp = await fetch("/api/v1/jobs/export", {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    const blob = await resp.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "jobpilot_jobs.csv";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <>
      <Typography variant="h5" gutterBottom>
        Jobs
      </Typography>

      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
          <TextField
            size="small" label="Title contains" value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && setApplied(q)}
          />
          <TextField select size="small" label="Arrangement" value={arrangement}
                     onChange={(e) => setArrangement(e.target.value)}
                     sx={{ minWidth: 140 }}>
            {ARRANGEMENTS.map((a) => (
              <MenuItem key={a} value={a}>{a || "Any"}</MenuItem>
            ))}
          </TextField>
          <TextField select size="small" label="Workplace" value={workplace}
                     onChange={(e) => setWorkplace(e.target.value)}
                     sx={{ minWidth: 140 }}>
            {WORKPLACES.map((w) => (
              <MenuItem key={w} value={w}>{w || "Any"}</MenuItem>
            ))}
          </TextField>
          <Button variant="contained" startIcon={<Search />}
                  onClick={() => setApplied(q)}>
            Filter
          </Button>
          <Button variant="outlined" onClick={() => runSearch.mutate()}
                  disabled={runSearch.isPending}>
            {runSearch.isPending ? "Queued…" : "Run new search"}
          </Button>
          <Button variant="text" onClick={exportCsv}>
            Export CSV
          </Button>
        </Stack>
      </Paper>

      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Title</TableCell>
              <TableCell>Location</TableCell>
              <TableCell>Type</TableCell>
              <TableCell>Source</TableCell>
              <TableCell>Salary</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {(data?.items ?? []).map((job) => (
              <TableRow key={job.id} hover>
                <TableCell>
                  <Link href={job.url} target="_blank" rel="noreferrer">
                    {job.title}
                  </Link>
                </TableCell>
                <TableCell>{job.location_text || "—"}</TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5}>
                    <Chip label={job.employment} size="small" />
                    {job.arrangement !== "UNSPECIFIED" && (
                      <Chip label={job.arrangement} size="small" color="primary" />
                    )}
                  </Stack>
                </TableCell>
                <TableCell>{job.connector_id}</TableCell>
                <TableCell>
                  {job.salary_max
                    ? `$${Math.round(job.salary_max / 1000)}k`
                    : "—"}
                </TableCell>
                <TableCell align="right">
                  <Button size="small" startIcon={<PlaylistAdd />}
                          onClick={() => track.mutate(job.id!)}>
                    Track
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {!isLoading && !(data?.items ?? []).length && (
              <TableRow>
                <TableCell colSpan={6}>
                  <Typography color="text.secondary" variant="body2" sx={{ p: 1 }}>
                    No jobs yet — hit "Run new search" (requires the worker) or
                    wait for the 6 AM ingestion.
                  </Typography>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
    </>
  );
}
