// saveUtils.ts

//strips file ext from filename string (recording.bag -> recording)
const stripExtension = (filename: string) => filename.replace(/\.[^/.]+$/, ""); 

// Builds the default annotation name shown when the save dialog opens
export const buildDefaultAnnotationName = (
    rosBagFileName: string,
    bookListFileName?: string
    ): string => {
    return `${stripExtension(rosBagFileName)}+${
        bookListFileName ? stripExtension(bookListFileName) : "noBookList"
    }`;
};

// Checks if the given annotation name is sensible. 
// Checks if name is empty, or contains any invalid characters
// returns reason for invalid name for error handling
export const isValidAnnotationName = (name: string): { valid: boolean; reason?: string } => {
    const trimmed = name.trim();

    if (!trimmed) {
        return { valid: false, reason: "Name cannot be empty." };
    }

    if (/[\\/:*?"<>|]/.test(trimmed)) {
        return { valid: false, reason: 'Name cannot contain any of: \\ / : * ? " < > |' };
    }

    if (/^\.+$/.test(trimmed)) {
        return { valid: false, reason: "Name cannot consist of only dots." };
    }

    return { valid: true };
};

//Collects the current annotation state into the JSON shape the backend expects
export const collectAnnotationData = (axes: any[]) => { 
    const data = axes.map((axis) => ({
        id: axis.id,
        axisType: axis.type,
        axisName: axis.axisName ? axis.axisName : "",
        axisBooklistName: axis.typeName ? axis.typeName : "",
        annotationBlocks: axis.blocks
        ? axis.blocks.map((block) => ({
            start: block.start,
            end: block.end,
            text: block.text,
            }))
        : [],
    }));
    console.log(data);
    return data;
};

export type AnnotationSaveConflict = {
    reason: "file_exists" | "file_unreadable";
    annotation_name: string;
    modified_at?: string;
    axis_count?: number;
    block_count?: number;
};

export type AnnotationSaveResult =
    | { status: "saved" }
    | { status: "conflict"; conflict: AnnotationSaveConflict };

// DRF mirrors the shape of the data it validated, so nested serializers
// produce nested errors. Flatten to the strings underneath.
const collectMessages = (value: unknown): string[] => {
    if (typeof value === "string") return [value];
    if (Array.isArray(value)) return value.flatMap(collectMessages);
    if (value && typeof value === "object") {
        return Object.values(value).flatMap(collectMessages);
    }
    return [];
};

export const postAnnotation = async (
    annotationName: string,
    annotationData: any,
    options?: { confirmOverwrite?: boolean }
    ): Promise<AnnotationSaveResult> => {
    const response = await fetch("http://localhost:8000/api/save_annotation/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
        annotation_name: annotationName,
        annotation_data: annotationData,
        confirm_overwrite: options?.confirmOverwrite ?? false,
        }),
    });

    if (response.ok) {
        return { status: "saved" };
    }

    if (response.status === 409) {
        const conflict = await response.json().catch(() => ({
            reason: "file_exists",
            annotation_name: annotationName,
        }));
        return { status: "conflict", conflict };
    }

    if (response.status === 400) {
        const errors = await response.json().catch(() => null);
        const messages = errors ? collectMessages(errors) : [];
        throw new Error(
            messages.length
                ? messages.join(" ")
                : "The annotation could not be saved."
        );
    }

    switch (response.status) {
    case 500:
        throw new Error("Internal server error");
    case 405:
        throw new Error("Method not allowed");
    default:
        throw new Error(`Unexpected error: ${response.status}`);
    }
};