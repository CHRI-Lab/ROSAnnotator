import React from 'react';
import { Paper, styled, Tooltip } from '@mui/material';
import Block from '../Block'; 

interface BlockData {
  start: number;
  end: number;
  text?: string;
}

interface AxisProps {
  duration: number;
  selectedRange: number[];
  blocks: BlockData[];
  axisType: string;
  typeName?: string; 
  annotations:any,
  onSave: (index: number, text: string) => void;
  onDeleteBlock: (index: number) => void;
}

const AxisContainer = styled(Paper)(({ theme }) => ({
  backgroundColor: theme.palette.background.paper,
  border: `1px solid ${theme.palette.divider}`,
  padding: '10px',
  marginTop: '10px',
  position: 'relative',
  width: '100%',
  minHeight: '30px',
}));

const Axis: React.FC<AxisProps> = ({ duration, selectedRange, blocks, axisType, typeName,annotations, onSave, onDeleteBlock }) => {
  return (
    <AxisContainer>
      {blocks.map((block, index) => (
        <Tooltip title={typeName || ''} key={index} placement="top" arrow>
          <div>
            <Block
              block={block}
              duration={duration}
              axisType={axisType}
              annotations={annotations}
              onSave={(text) => onSave(index, text)}
              onDelete={() => onDeleteBlock(index)}
            />
          </div>
        </Tooltip>
      ))}
    </AxisContainer>
  );
};

export default Axis;
