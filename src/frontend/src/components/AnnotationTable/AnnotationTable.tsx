import React, { useContext, useEffect, useState } from 'react';
import { Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper } from '@mui/material';
import AxesContext from '../AxesProvider';

interface TableData {
    beginTime: number; // in seconds
    endTime: number; // in seconds
    duration: number; // in seconds
    tierName: string;
    annotation: string;
}

const AnnotationTable: React.FC = () => {
    const { axes, } = useContext(AxesContext)!;

    const [rows, setRows] = useState<TableData[]>([]);

    // Function to calculate duration based on input time in seconds
    const calculateDuration = (begin: number, end: number) => {
        return end - begin;
    };

    useEffect(() => {
        const newRows: TableData[] = [];
        axes.forEach(axis => {
            axis.blocks.forEach(block => {
                newRows.push({
                    beginTime: block.start,
                    endTime: block.end,
                    duration: calculateDuration(block.start, block.end),
                    tierName: axis.typeName || "undefined",
                    annotation: block.text || ''
                });
            });
        });
        setRows(newRows);
    }, [axes]);
    
    const formatTime = (seconds: number) => {
        return (seconds).toFixed(1); // Converts to hours and rounds to 0.1
    };

    return (
        <TableContainer component={Paper} style={{ maxHeight: 452, overflow: 'auto' }}>
            <Table stickyHeader aria-label="scrollable table">
                <TableHead>
                    <TableRow>
                        <TableCell>Begin Time</TableCell>
                        <TableCell>End Time</TableCell>
                        <TableCell>Duration</TableCell>
                        <TableCell>Tier Name</TableCell>
                        <TableCell>Annotation</TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {rows.map((row, index) => (
                        <TableRow
                            key={index}
                            sx={{ '&:last-child td, &:last-child th': { border: 0 } }}
                        >
                            <TableCell component="th" scope="row">
                                {formatTime(row.beginTime)}
                            </TableCell>
                            <TableCell>
                                {formatTime(row.endTime)}
                            </TableCell>
                            <TableCell>{formatTime(row.duration)}</TableCell>
                            <TableCell>{row.tierName}</TableCell>
                            <TableCell>{row.annotation}</TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </TableContainer>
    );
};

export default AnnotationTable;
