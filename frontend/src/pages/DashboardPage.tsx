import { Card, CardContent, Grid2 as Grid, Skeleton, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

const KPIS = [
  { key: "jobs_found", label: "Jobs found" },
  { key: "jobs_applied", label: "Applied" },
  { key: "interviews", label: "Interviews" },
  { key: "offers", label: "Offers" },
  { key: "rejections", label: "Rejections" },
  { key: "success_rate", label: "Success rate %" },
] as const;

export default function DashboardPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => (await api.GET("/analytics/dashboard")).data,
  });

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
                  <Typography variant="h4">{data?.[kpi.key] ?? 0}</Typography>
                )}
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 3 }}>
        Charts (applications by week, match and salary distributions, hiring
        trends, tech demand) land in Phase 9.
      </Typography>
    </>
  );
}
