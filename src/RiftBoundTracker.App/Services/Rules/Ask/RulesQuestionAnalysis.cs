namespace RiftBoundTracker.App.Services.Rules;

public sealed record DetectedKeywordDto(int Id, string Name, string? MatchedAlias);
public sealed record DetectedConceptDto(int Id, string Name, string? MatchedPhrase);

public sealed record RulesQuestionAnalysis(
    string OriginalQuestion,
    string NormalizedQuestion,
    List<string> DetectedRuleNumbers,
    List<DetectedKeywordDto> DetectedKeywords,
    List<DetectedConceptDto> DetectedConcepts,
    List<CardSummaryDto> CardContext,
    List<string> ExpandedTerms);
