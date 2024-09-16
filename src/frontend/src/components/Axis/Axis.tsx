import React from 'react';
import { Paper, styled } from '@mui/material';
import Block from '../Block';
import { Droppable, Draggable } from 'react-beautiful-dnd';

interface BlockData {
  start: number;
  end: number;
  text?: string;
}

interface AxisProps {
  id: number;
  duration: number;
  selectedRange: number[];
  blocks: BlockData[];
  axisType: string;
  axisName?: string;
  onSave: (index: number, text: string,start: number, end: number) => void;
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
  zIndex: 1,
}));

const Axis: React.FC<AxisProps> = ({ id, duration, blocks, axisType, axisName, onSave, onDeleteBlock }) => {
  return (
    <Droppable droppableId={String(id)}>
      {(provided) => (
        <AxisContainer ref={provided.innerRef} {...provided.droppableProps}>
          <TypeName>{axisName || 'No axis Name'}</TypeName>
          {blocks.map((block, index) => (
            <Draggable key={`block-${id}-${block.start}`} draggableId={String(`block-${id}-${block.start}`)} index={index}>
              {(provided) => (
                <div
                  ref={provided.innerRef}
                  {...provided.draggableProps}
                  {...provided.dragHandleProps}
                  style={{ ...provided.draggableProps.style, marginBottom: '8px' }}  // Add spacing between blocks
                >
                  <Block
                    block={block}
                    duration={duration}
                    axisType={axisType}
                    onSave={(text, start, end) => onSave(index, text, start, end)}  // Pass the start, end, and text back to onSave
                    onDelete={() => onDeleteBlock(index)}
                  />
                </div>
              )}
            </Draggable>
          ))}
          {provided.placeholder}
        </AxisContainer>
      )}
    </Droppable>
  );
};

export default Axis;