import { CircularProgress, Box, Typography } from "@mui/material";

const LoadingPage = () => {
  return (
    <Box
      sx={{
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        height: "100vh",
        backgroundColor: "#f0f0f0",
      }}
    >
      <CircularProgress />
      <Typography
        sx={{
          marginTop: 2,
        }}
        variant="h6"
        color="textSecondary"
      >
        We are processing your data ...
      </Typography>
    </Box>
  );
};

export default LoadingPage;
