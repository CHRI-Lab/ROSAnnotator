import React, { useState } from 'react';
import { Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, TextField } from '@mui/material';

interface TableData {
    beginTime: string;
    endTime: string;
    duration: string;
    tierName: string;
    annotation: string;
}

const initialRows: TableData[] = [
    { beginTime: "08:00", endTime: "09:15", duration: "", tierName: "Gold", annotation: "Meeting" },
    { beginTime: "10:00", endTime: "10:45", duration: "", tierName: "Silver", annotation: "Training" },
    { beginTime: "08:00", endTime: "09:15", duration: "", tierName: "Gold", annotation: "Meeting" },
    { beginTime: "10:00", endTime: "10:45", duration: "", tierName: "Silver", annotation: "Training" },
    { beginTime: "08:00", endTime: "09:15", duration: "", tierName: "Gold", annotation: "Meeting" },
    { beginTime: "10:00", endTime: "10:45", duration: "", tierName: "Silver", annotation: "Training" },
    // Add more rows as needed
];

const AnnotationTable: React.FC = () => {
    const [rows, setRows] = useState<TableData[]>(initialRows);

    // Function to calculate duration based on input time strings
    const calculateDuration = (begin: string, end: string) => {
        const startTime = new Date(`2021-01-01T${begin}:00`);
        const endTime = new Date(`2021-01-01T${end}:00`);
        const diff = endTime.getTime() - startTime.getTime();

        const totalSeconds = Math.floor(diff / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;

        if (hours > 0) {
            return `${hours} hour${hours > 1 ? 's' : ''}`;
        } else if (minutes > 0) {
            return `${minutes} minute${minutes > 1 ? 's' : ''}`;
        } else {
            return `${seconds} second${seconds > 1 ? 's' : ''}`;
        }
    };

    const handleChange = (index: number, field: keyof TableData, value: string) => {
        const newRows = [...rows];
        const row = newRows[index];
        row[field] = value;

        if (field === 'beginTime' || field === 'endTime') {
            if (row.beginTime && row.endTime) {
                row.duration = calculateDuration(row.beginTime, row.endTime);
            }
        }

        setRows(newRows);
    };

    return (
        <TableContainer component={Paper} style={{ maxHeight: 400, overflow: 'auto' }}>
            <Table sx={{ minWidth: 650 }} stickyHeader aria-label="scrollable table">
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
                                <TextField
                                    value={row.beginTime}
                                    onChange={(e) => handleChange(index, 'beginTime', e.target.value)}
                                    size="small"
                                />
                            </TableCell>
                            <TableCell>
                                <TextField
                                    value={row.endTime}
                                    onChange={(e) => handleChange(index, 'endTime', e.target.value)}
                                    size="small"
                                />
                            </TableCell>
                            <TableCell>{row.duration}</TableCell>
                            <TableCell>
                                <TextField
                                    value={row.tierName}
                                    onChange={(e) => handleChange(index, 'tierName', e.target.value)}
                                    size="small"
                                />
                            </TableCell>
                            <TableCell>
                                <TextField
                                    value={row.annotation}
                                    onChange={(e) => handleChange(index, 'annotation', e.target.value)}
                                    size="small"
                                />
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </TableContainer>
    );
};

export default AnnotationTable;
