import React from 'react';
import jsonData from '../../../public/predefined_booklist.json';
import { Grid } from '@mui/material';

const Booklist: React.FC = () => {
    return (
        <Grid container spacing={2}>
            {Object.entries(jsonData).map(([category, words], index) => (
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
