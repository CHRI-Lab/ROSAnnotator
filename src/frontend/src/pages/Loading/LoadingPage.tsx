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
      <Typography
        sx={{
          fontSize: 16,
          fontStyle: "italic",
        }}
        variant="h6"
        color="textSecondary"
      >
        Audio transcription can take a few minutes.
      </Typography>
    </Box>
  );
};

export default LoadingPage;
