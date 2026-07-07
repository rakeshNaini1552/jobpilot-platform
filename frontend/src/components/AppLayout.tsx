import {
  AutoAwesome, Dashboard, Description, Logout, Settings,
  SmartToy, TableChart, Tune, WorkOutline,
} from "@mui/icons-material";
import {
  AppBar, Box, Drawer, IconButton, List, ListItemButton, ListItemIcon,
  ListItemText, Toolbar, Typography,
} from "@mui/material";
import { NavLink, Outlet } from "react-router-dom";
import { useAuthStore } from "@/stores/auth";

const DRAWER_WIDTH = 232;

const NAV = [
  { to: "/", label: "Dashboard", icon: <Dashboard /> },
  { to: "/jobs", label: "Jobs", icon: <WorkOutline /> },
  { to: "/tracker", label: "Tracker", icon: <TableChart /> },
  { to: "/assistant", label: "Assistant", icon: <SmartToy /> },
  { to: "/resumes", label: "Resumes", icon: <Description /> },
  { to: "/preferences", label: "Preferences", icon: <Tune /> },
];

export function AppLayout() {
  const { user, logout } = useAuthStore();
  return (
    <Box sx={{ display: "flex" }}>
      <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar>
          <AutoAwesome sx={{ mr: 1 }} />
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            JobPilot
          </Typography>
          <Typography variant="body2" sx={{ mr: 2 }}>
            {user?.full_name}
          </Typography>
          <IconButton color="inherit" aria-label="log out" onClick={logout}>
            <Logout />
          </IconButton>
        </Toolbar>
      </AppBar>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          [`& .MuiDrawer-paper`]: { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
      >
        <Toolbar />
        <List>
          {NAV.map((item) => (
            <ListItemButton
              key={item.to}
              component={NavLink}
              to={item.to}
              sx={{ "&.active": { bgcolor: "action.selected" } }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
          {user?.role === "ADMIN" && (
            <ListItemButton component={NavLink} to="/admin"
              sx={{ "&.active": { bgcolor: "action.selected" } }}>
              <ListItemIcon><Settings /></ListItemIcon>
              <ListItemText primary="Admin" />
            </ListItemButton>
          )}
        </List>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar />
        <Outlet />
      </Box>
    </Box>
  );
}
