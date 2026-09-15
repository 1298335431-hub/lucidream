import AppKit
import Foundation
import Vision

struct OCRLine: Codable {
    let text: String
    let confidence: Float
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct OCRDocument: Codable {
    let image: String
    let languages: [String]
    let lines: [OCRLine]
}

guard CommandLine.arguments.count == 2 else {
    fputs("usage: vision_ocr.swift IMAGE\n", stderr)
    exit(2)
}

let imagePath = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: imagePath) else {
    fputs("unable to open image\n", stderr)
    exit(3)
}

var proposedRect = NSRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &proposedRect, context: nil, hints: nil) else {
    fputs("unable to decode image\n", stderr)
    exit(4)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hant", "zh-Hans"]
request.minimumTextHeight = 0.008

do {
    try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
} catch {
    fputs("OCR failed\n", stderr)
    exit(5)
}

let observations = (request.results ?? []).compactMap { observation -> OCRLine? in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let box = observation.boundingBox
    return OCRLine(
        text: candidate.string,
        confidence: candidate.confidence,
        x: box.origin.x,
        y: box.origin.y,
        width: box.size.width,
        height: box.size.height
    )
}

// Traditional scans are normally vertical and ordered from the rightmost
// column to the left. Keep geometry in the output so later review can repair
// exceptional horizontal headings without losing provenance.
let ordered = observations.sorted {
    let xDelta = $0.x - $1.x
    if abs(xDelta) > 0.015 { return $0.x > $1.x }
    return $0.y > $1.y
}

let document = OCRDocument(
    image: URL(fileURLWithPath: imagePath).lastPathComponent,
    languages: request.recognitionLanguages,
    lines: ordered
)

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys, .withoutEscapingSlashes]
do {
    let data = try encoder.encode(document)
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
} catch {
    fputs("unable to encode OCR result\n", stderr)
    exit(6)
}
