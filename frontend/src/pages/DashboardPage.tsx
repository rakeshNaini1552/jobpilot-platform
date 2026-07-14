import {
  Card, CardContent, Grid2 as Grid, Link, Skeleton, Stack, Table, TableBody,
  TableCell, TableHead, TableRow, Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import {
  Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { api } from "@/api/client";

const SERIES = "#1a56db"; // validated: dataviz palette checks pass on light surface
const GRID = "#e6e9ef";
const AXIS = { fontSize: 12, fill: "#6b7280" };

const KPIS = [
  { key: "jobs_found", label: "Jobs found" },
  { key: "jobs_applied", label: "Applied" },
  { key: "interviews", label: "Interviews" },
  { key: "offers", label: "Offers" },
  { key: "rejections", label: "Rejections" },
  { key: "success_rate", label: "Success rate %" },
] as const;

function ChartCard({ title, children }: { title: string; children: React.ReactElement }) {
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle2" color="text.secondary" gutterBottom>
          {title}
        </Typography>
        <ResponsiveContainer width="100%" height={220}>
          {children}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await api.GET("/api/v1/analytics/dashboard")).data,
  });

  const byWeek = data?.applications_by_week ?? [];
  const scoreDist = data?.match_score_distribution ?? [];

  return (
    <>
      <Typography variant="h5" gutterBottom>
        Dashboard
      </Typography>

      <Grid container spacing={2}>
        {KPIS.map((kpi) => (
          <Grid key={kpi.key} size={{ xs: 6, sm: 4, md: 2 }}>
            <Card>
              <CardContent>
                <Typography variant="body2" color="text.secondary">
                  {kpi.label}
                </Typography>
                {isLoading ? (
                  <Skeleton width={48} height={40} />
                ) : (
                  <Typography variant="h4">
                    {(data as Record<string, unknown> | undefined)?.[kpi.key] as number ?? 0}
                  </Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}

        <Grid size={{ xs: 12, md: 6 }}>
          <ChartCard title="Applications by week">
            <BarChart data={byWeek} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="week" tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(26,86,219,0.06)" }} />
              <Bar dataKey="count" name="Applications" fill={SERIES}
                   barSize={28} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartCard>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <ChartCard title="Match score distribution">
            <BarChart data={scoreDist} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="bucket" tick={AXIS} tickLine={false} axisLine={false} />
              <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} />
              <Tooltip cursor={{ fill: "rgba(26,86,219,0.06)" }} />
              <Bar dataKey="count" name="Jobs" fill={SERIES}
                   barSize={28} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartCard>
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Top matches
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Role</TableCell>
                    <TableCell align="right">Score</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(data?.top_matches ?? []).map((m) => (
                    <TableRow key={m.url}>
                      <TableCell>
                        <Link href={m.url ?? "#"} target="_blank" rel="noreferrer">
                          {m.title}
                        </Link>
                      </TableCell>
                      <TableCell align="right">{Math.round(m.score ?? 0)}</TableCell>
                    </TableRow>
                  ))}
                  {!isLoading && !(data?.top_matches ?? []).length && (
                    <TableRow>
                      <TableCell colSpan={2}>
                        <Typography color="text.secondary" variant="body2">
                          No scored matches yet — run a search from the Jobs page.
                        </Typography>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 5 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" color="text.secondary" gutterBottom>
                Suggestions
              </Typography>
              <Stack spacing={1}>
                {(data?.ai_suggestions ?? []).map((s) => (
                  <Typography key={s} variant="body2">• {s}</Typography>
                ))}
                {!isLoading && !(data?.ai_suggestions ?? []).length && (
                  <Typography color="text.secondary" variant="body2">
                    Suggestions appear once jobs are matched against your resume.
                  </Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </>
  );
}
