# فرهنگ داده

| فایل | ستون | معنا |
|---|---|---|
| ratings.csv | userId | شناسه ناشناس کاربر |
| ratings.csv | movieId | شناسه فیلم |
| ratings.csv | rating | امتیاز 0.5 تا 5 |
| ratings.csv | timestamp | زمان ثبت امتیاز، Unix timestamp |
| movies.csv | movieId | شناسه فیلم |
| movies.csv | title | عنوان فیلم |
| movies.csv | genres | ژانرها با جداکننده `|` |
| tags.csv | userId | شناسه کاربر ثبت‌کننده برچسب |
| tags.csv | movieId | شناسه فیلم |
| tags.csv | tag | برچسب متنی |
| tags.csv | timestamp | زمان ثبت برچسب |
| links.csv | movieId | شناسه فیلم |
| links.csv | imdbId | شناسه IMDb |
| links.csv | tmdbId | شناسه TMDb |

کلید اتصال دو جدول اصلی `movieId` است. برای تحلیل تعاملات، `userId` نیز شناسه کاربر را مشخص می‌کند.
