import Vision
import Foundation
let dir = CommandLine.arguments[1]
let files = try! FileManager.default.contentsOfDirectory(atPath: dir).filter { $0.hasSuffix(".png") }.sorted()
var out: [String: String] = [:]
for f in files {
  let req = VNRecognizeTextRequest()
  req.recognitionLevel = .accurate; req.recognitionLanguages = ["en-US"]; req.usesLanguageCorrection = true
  try! VNImageRequestHandler(url: URL(fileURLWithPath: dir + "/" + f)).perform([req])
  let lines = (req.results ?? []).sorted { $0.boundingBox.minX < $1.boundingBox.minX }.compactMap { $0.topCandidates(1).first?.string }
  out[String(Int(f.dropLast(4))!)] = lines.joined(separator: " ")
}
print(String(data: try! JSONSerialization.data(withJSONObject: out, options: [.sortedKeys]), encoding: .utf8)!)
