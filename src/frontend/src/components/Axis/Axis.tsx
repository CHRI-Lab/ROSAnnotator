import React from 'react';
import { Paper, styled } from '@mui/material';
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
  axisName?: string;
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
  minHeight: '50px',  
}));

const TypeName = styled('div')(() => ({
  position: 'absolute',
  width: '100%',
  top: 0,  
  left: 0,
  color: '#999',
  fontStyle: 'italic',
  padding: '0 10px',
  fontSize: '0.8rem',
  zIndex: 1  
}));

const Axis: React.FC<AxisProps> = ({ duration, blocks, axisType, typeName, axisName, annotations, onSave, onDeleteBlock }) => {
  return (
    <AxisContainer>
      <TypeName>{axisName || 'No axis Name'}</TypeName>
      {blocks.map((block, index) => (
        <Block
          key={index}
          block={block}
          duration={duration}
          axisType={axisType}
          annotations={annotations}
          onSave={(text) => onSave(index, text)}
          onDelete={() => onDeleteBlock(index)}
        />
      ))}
    </AxisContainer>
  );
};

export default Axis;
