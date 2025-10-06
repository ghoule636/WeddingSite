using System;
using Microsoft.AspNetCore.Components;

namespace WeddingSite;

public static class LanguageHelper
{
    public const string English = "en";
    public const string Spanish = "es";

    public static string AppendLanguageQuery(string path, string? language) =>
        language is null ? path : $"{path}?lang={language}";

    public static string? GetLanguageFromUri(NavigationManager navigation)
    {
        var absoluteUri = navigation.ToAbsoluteUri(navigation.Uri);
        var rawQuery = absoluteUri.Query;

        if (string.IsNullOrEmpty(rawQuery))
        {
            return null;
        }

        var parameters = rawQuery.TrimStart('?').Split('&', StringSplitOptions.RemoveEmptyEntries);

        foreach (var parameter in parameters)
        {
            var parts = parameter.Split('=', 2, StringSplitOptions.RemoveEmptyEntries);

            if (parts.Length == 2 &&
                parts[0].Equals("lang", StringComparison.OrdinalIgnoreCase))
            {
                var value = Uri.UnescapeDataString(parts[1]);

                return IsSupportedLanguage(value) ? value : null;
            }
        }

        return null;
    }

    public static bool IsSupportedLanguage(string? language) =>
        language is English or Spanish;

    public static void NavigateToCurrentWithLanguage(NavigationManager navigation, string? language)
    {
        var absoluteUri = navigation.ToAbsoluteUri(navigation.Uri);
        var baseUri = absoluteUri.GetLeftPart(UriPartial.Path);
        var destination = AppendLanguageQuery(baseUri, language);

        navigation.NavigateTo(destination);
    }
}
