import React from "react";
import { Grid } from "@mui/material";

interface BooklistProps {
  bookListData: Record<string, string[]>;
}

const Booklist: React.FC<BooklistProps> = ({ bookListData }) => {
  return (
    <Grid container spacing={2}>
      {Object.entries(bookListData).map(([category, words], index) => (
        <Grid item xs={12} sm={6} md={4} key={index}>
          <h3>{category}</h3>
          <ul>
            {words.map((word, wordIndex) => (
              <li key={wordIndex}>{word}</li>
            ))}
          </ul>
        </Grid>
      ))}
    </Grid>
  );
};

export default Booklist;
