import { CSSProperties, useCallback } from "react";
import { styled } from '@mui/system';
import { Lrc, LrcLine } from "react-lrc";
import { Box } from "@mui/material";

interface TranscriptProps {
  played: number;
}

const LRC = `[00:00]Okay, since we already published the second and the third one, I'm going to post the first one
[00:07.76]with me and the sixth one next to it. I can't reach the other side. Can you please turn the
[00:17.36]white thing around? I will work on that. Thank you.
[00:29.12]I'm sorry, you can only polish the base step is facing you. Okay. Okay, okay. I think I did it
[00:41.60]like the first one, the second one and the sixth one. Okay, the high-diago.
[00:49.44]High-diago.
[00:54.72]All right, how can I help you first? Okay, can you turn the price around?
[01:03.12]Please turn it. We'll work on that. Opposites.
[01:06.64]Okay.
[01:24.24]Oh, okay. I'm going to polish that. So, we have another two surfaces to polish. Can you turn around
[01:36.32]that for me? Yes, I can. You can start. Sure.
[01:48.32]Do you need any help?
[02:00.32]Yeah, go. This trial is like, polish the one facing you. Only this one. Only. Yeah, yeah. So, not the side ones,
[02:18.40]but when it turns to face you. Okay. Yeah, I got it. Okay, it's okay. Okay, so we need to do six times.
[02:28.56]I was going to do six times. Yeah, but I mean, I guess since you've already polished like the
[02:34.64]other size, just polish like your remaining ones. Yeah. Yeah. Okay. Okay, the remaining one is the
[02:41.92]fours one and the fifth one. Can you? Hi, Tio. Can you help me turn turning again? Sure.
[03:42.32]Okay. Thank you. Okay, I finished the fourth one and we have the last one to finish, which is
[03:49.44]some surface five. Can you turn it again? Yes, I can. Okay. Please.
[04:11.92]Okay. Okay. Thank you. Okay. I finished. I think we can't leave the task. Thank you.
[04:35.84]Oh, you're great. All right. Yeah. Nice job. We're going to serve it. Yeah. Thank you, Thiago. Okay, response.
[04:49.60]I'm happy to hear that. Oh, yeah.
[05:05.84]Yeah.`;

const lrcStyle: CSSProperties = {
  flex: 1,
  minHeight: 0
};

const Line = styled('div')<{ active: boolean }>`
  min-height: 10px;
  padding: 5px 20px;

  font-size: 16px;
  text-align: center;

  ${({ active }) => `
    color: ${active ? "dodgerblue" : "black"};
  `}
`;

const Transcript: React.FC<TranscriptProps> = ({ played }) => {

  const lineRenderer = useCallback(
    ({ active, line: { content } }: { active: boolean; line: LrcLine }) => (
      <Line active={active}>{content}</Line>
    ),
    []
  );

  return (
    <Box
      width="100%"
      height="100%"
      display="flex"
      flexDirection="column"
      sx={{
        bgcolor: 'lightgray',
      }}
    >
      <Lrc
        lrc={LRC}
        lineRenderer={lineRenderer}
        currentMillisecond={played*1000}
        verticalSpace
        style={lrcStyle}
        recoverAutoScrollInterval={5000}
      />
    </Box>
  );
};

export default Transcript;
