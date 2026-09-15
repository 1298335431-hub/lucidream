import Foundation
import Vision

struct Observation: Encodable {
    let text: String
    let confidence: Float
    let x: CGFloat
    let y: CGFloat
    let width: CGFloat
    let height: CGFloat
}

struct PageResult: Encodable {
    let page: Int
    let image: String
    let readingOrder: String
    let rawText: String
    let observations: [Observation]
}

func pageNumber(for url: URL) -> Int? {
    let base = url.deletingPathExtension().lastPathComponent
    let digits = base.reversed().prefix { $0.isNumber }.reversed()
    return Int(String(digits))
}

func writeLine<T: Encodable>(_ value: T, to handle: FileHandle) throws {
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    var data = try encoder.encode(value)
    data.append(0x0A)
    handle.write(data)
}

let arguments = CommandLine.arguments
guard arguments.count == 3 else {
    fputs("Usage: ocr_vision_traditional.swift <rendered-image-directory> <output-jsonl>\n", stderr)
    exit(2)
}

let imageDirectory = URL(fileURLWithPath: arguments[1], isDirectory: true)
let outputURL = URL(fileURLWithPath: arguments[2])
let fileManager = FileManager.default

let imageURLs = try fileManager.contentsOfDirectory(
    at: imageDirectory,
    includingPropertiesForKeys: nil,
    options: [.skipsHiddenFiles]
).filter { ["png", "jpg", "jpeg"].contains($0.pathExtension.lowercased()) }
 .sorted { (pageNumber(for: $0) ?? 0) < (pageNumber(for: $1) ?? 0) }

guard !imageURLs.isEmpty else {
    fputs("No PNG/JPEG page images found.\n", stderr)
    exit(2)
}

fileManager.createFile(atPath: outputURL.path, contents: nil)
let output = try FileHandle(forWritingTo: outputURL)
defer { try? output.close() }

for imageURL in imageURLs {
    guard let page = pageNumber(for: imageURL) else {
        fputs("Cannot infer PDF page number from \(imageURL.lastPathComponent).\n", stderr)
        exit(2)
    }

    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["zh-Hant", "zh-Hans"]
    request.usesLanguageCorrection = false

    let handler = VNImageRequestHandler(url: imageURL, options: [:])
    try handler.perform([request])

    let observations = (request.results ?? []).compactMap { result -> Observation? in
        guard let candidate = result.topCandidates(1).first else { return nil }
        let box = result.boundingBox
        return Observation(
            text: candidate.string,
            confidence: candidate.confidence,
            x: box.origin.x,
            y: box.origin.y,
            width: box.width,
            height: box.height
        )
    }.sorted {
        // The source is vertical Chinese. Columns are ordered right-to-left;
        // within each column, segments are ordered top-to-bottom.
        if abs($0.x - $1.x) > 0.012 { return $0.x > $1.x }
        return $0.y > $1.y
    }

    try writeLine(PageResult(
        page: page,
        image: imageURL.lastPathComponent,
        readingOrder: "right_to_left_columns_then_top_to_bottom",
        rawText: observations.map(\.text).joined(separator: "\n"),
        observations: observations
    ), to: output)
}
